/** @type {import('@commitlint/types').UserConfig} */
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Allow scopes relevant to this project
    'scope-enum': [
      2,
      'always',
      [
        'backend',
        'frontend',
        'docker',
        'ci',
        'deps',
        'config',
        'docs',
        'agents',
        'scraper',
        'api',
        'db',
        'celery',
        'auth',
        'alerts',
        'make',
        'todo',
        'quality',
        'plan-review',
        'e2e',
        'security',
      ],
    ],
    // Subject must not end with a period
    'subject-full-stop': [2, 'never', '.'],
    // Reject all-caps, title-case, or sentence-case subjects while allowing
    // lowercase and uppercase acronyms (e.g. "fix CI failures" is valid).
    'subject-case': [2, 'never', ['sentence-case', 'start-case', 'pascal-case', 'upper-case']],
    // Header max length
    'header-max-length': [2, 'always', 100],
  },
};
