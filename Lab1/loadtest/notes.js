import http from 'k6/http';
import { check, sleep, fail } from 'k6';
import { Counter, Rate } from 'k6/metrics';
import exec from 'k6/execution';

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const VUS = parseInt(__ENV.VUS || '60', 10);
const RAMP_UP = __ENV.RAMP_UP || '3m';
const STEADY = __ENV.STEADY || '5m';
const RAMP_DOWN = __ENV.RAMP_DOWN || '2m';
const THINK = parseFloat(__ENV.THINK || '0.3');
const MODE = (__ENV.MODE || 'sync').toLowerCase();
const LABEL = __ENV.LABEL || 'run';
const PAGE = 20;

const cacheHits = new Rate('cache_hits');
const writes = new Counter('writes');
const reads = new Counter('reads');

export const options = {
  scenarios: {
    users: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: RAMP_UP, target: VUS },
        { duration: STEADY, target: VUS },
        { duration: RAMP_DOWN, target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{kind:read}': ['p(95)<1500'],
    'http_req_duration{kind:write}': ['p(95)<3000'],
  },
  setupTimeout: '3m',
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const USERS = parseInt(__ENV.USERS || '5', 10);

const session = { token: null, userId: null, recentIds: [], lastJob: null };

function params(name, kind, extraHeaders) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, extraHeaders || {});
  if (session.token) {
    headers.Authorization = `Bearer ${session.token}`;
  }
  return { headers, tags: { name, kind } };
}

export function setup() {
  const users = [];
  const stamp = Date.now();
  for (let i = 0; i < USERS; i++) {
    const credentials = JSON.stringify({ username: `k6_${LABEL}_${stamp}_${i}`.slice(0, 50), password: 'load-test-password' });
    const headers = { headers: { 'Content-Type': 'application/json' }, tags: { name: 'setup', kind: 'setup' } };
    const registered = http.post(`${BASE_URL}/auth/register`, credentials, headers);
    if (registered.status !== 201) {
      fail(`register failed: ${registered.status}`);
    }
    const login = http.post(`${BASE_URL}/auth/login`, credentials, headers);
    if (login.status !== 200) {
      fail(`login failed: ${login.status}`);
    }
    users.push({ token: login.json('access_token'), userId: login.json('user_id') });
  }
  return { users };
}

function idempotencyKey() {
  return `${LABEL}-${exec.vu.idInTest}-${exec.vu.iterationInScenario}-${Date.now()}`;
}

function writeNote() {
  const body = JSON.stringify({
    title: `note from vu ${exec.vu.idInTest}`,
    body: `iteration ${exec.vu.iterationInScenario}`,
  });
  const headers = { 'Idempotency-Key': idempotencyKey() };
  writes.add(1);
  if (MODE === 'async') {
    const res = http.post(`${BASE_URL}/notes/async`, body, params('POST /notes/async', 'write', headers));
    check(res, { 'enqueue 202': (r) => r.status === 202 });
    session.lastJob = res.status === 202 ? res.json('job_id') : null;
    return null;
  }
  const res = http.post(`${BASE_URL}/notes`, body, params('POST /notes', 'write', headers));
  check(res, { 'create 201': (r) => r.status === 201 });
  return res.status === 201 ? res.json('id') : null;
}

function listNotes() {
  reads.add(1);
  const res = http.get(`${BASE_URL}/notes?limit=${PAGE}`, params('GET /notes', 'read'));
  check(res, { 'list 200': (r) => r.status === 200 });
  cacheHits.add(res.headers['X-Cache'] === 'HIT');
  if (res.status === 200) {
    const ids = res.json().map((n) => n.id);
    if (ids.length > 0) {
      session.recentIds = ids;
    }
  }
  return res;
}

function getNote(id) {
  reads.add(1);
  const res = http.get(`${BASE_URL}/notes/${id}`, params('GET /notes/{id}', 'read'));
  check(res, { 'note 200': (r) => r.status === 200 });
  return res;
}

function getUser(id) {
  reads.add(1);
  const res = http.get(`${BASE_URL}/users/${id}`, params('GET /users/{id}', 'read'));
  check(res, { 'user 200': (r) => r.status === 200 });
  return res;
}

function getJob() {
  reads.add(1);
  const res = http.get(`${BASE_URL}/jobs/${session.lastJob}`, params('GET /jobs/{id}', 'read'));
  check(res, { 'job 200': (r) => r.status === 200 });
  return res;
}

function randomRecentId(fallback) {
  if (session.recentIds.length === 0) {
    return fallback;
  }
  return session.recentIds[Math.floor(Math.random() * session.recentIds.length)];
}

function pause() {
  sleep(THINK * (0.5 + Math.random()));
}

export default function (data) {
  if (!session.token) {
    const user = data.users[(exec.vu.idInTest - 1) % data.users.length];
    session.token = user.token;
    session.userId = user.userId;
  }

  const createdId = writeNote();
  pause();

  listNotes();
  pause();
  if (createdId !== null) {
    getNote(createdId);
  } else if (session.lastJob) {
    getJob();
  } else {
    listNotes();
  }
  pause();
  getUser(session.userId);
  pause();
  listNotes();
  pause();
  const other = getNote(randomRecentId(createdId || 1));
  pause();
  listNotes();
  pause();
  if (createdId !== null) {
    getNote(createdId);
  } else {
    getNote(randomRecentId(1));
  }
  pause();
  const authorId = other.status === 200 && other.json('author_id') ? other.json('author_id') : session.userId;
  getUser(authorId);
  pause();
  listNotes();
  pause();
}

function metricValue(data, name, stat) {
  const metric = data.metrics[name];
  if (!metric || metric.values[stat] === undefined) {
    return null;
  }
  return metric.values[stat];
}

function ms(value) {
  return value === null ? '—' : `${value.toFixed(1)} ms`;
}

function pct(value) {
  return value === null ? '—' : `${(value * 100).toFixed(2)} %`;
}

function num(value, digits) {
  return value === null ? '—' : value.toFixed(digits);
}

function latencyRow(data, title, name) {
  return `| ${title} | ${ms(metricValue(data, name, 'med'))} | ${ms(metricValue(data, name, 'p(95)'))} | ${ms(metricValue(data, name, 'p(99)'))} | ${ms(metricValue(data, name, 'max'))} |`;
}

function report(data) {
  const started = new Date(Date.now() - data.state.testRunDurationMs).toISOString();
  return [
    `# Звіт навантажувального тесту: ${LABEL}`,
    '',
    `- Адреса: ${BASE_URL}`,
    `- Режим запису: ${MODE}`,
    `- Профіль: 0 → ${VUS} VU за ${RAMP_UP}, ${VUS} VU ${STEADY}, ${VUS} → 0 за ${RAMP_DOWN}; пауза між запитами ~${THINK} с; ${USERS} тестових акаунтів`,
    `- Початок (UTC): ${started}`,
    `- Тривалість: ${(data.state.testRunDurationMs / 60000).toFixed(1)} хв`,
    '',
    '| Показник | Значення |',
    '|---|---|',
    `| Усього HTTP-запитів | ${num(metricValue(data, 'http_reqs', 'count'), 0)} |`,
    `| Запитів за секунду (середнє) | ${num(metricValue(data, 'http_reqs', 'rate'), 1)} |`,
    `| Операцій запису | ${num(metricValue(data, 'writes', 'count'), 0)} |`,
    `| Операцій читання | ${num(metricValue(data, 'reads', 'count'), 0)} |`,
    `| Частка помилок | ${pct(metricValue(data, 'http_req_failed', 'rate'))} |`,
    `| Частка влучань у кеш (GET /notes) | ${pct(metricValue(data, 'cache_hits', 'rate'))} |`,
    '',
    '| Латентність | p50 | p95 | p99 | max |',
    '|---|---|---|---|---|',
    latencyRow(data, 'Усі запити', 'http_req_duration'),
    latencyRow(data, 'Читання', 'http_req_duration{kind:read}'),
    latencyRow(data, 'Запис', 'http_req_duration{kind:write}'),
    '',
  ].join('\n');
}

export function handleSummary(data) {
  const md = report(data);
  return {
    stdout: `\n${md}\n`,
    [`results/${LABEL}.md`]: md,
    [`results/${LABEL}.json`]: JSON.stringify(data, null, 2),
  };
}
