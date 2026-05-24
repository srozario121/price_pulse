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
      ],
    ],
    // Subject must not end with a period
    'subject-full-stop': [2, 'never', '.'],
    // Subject must start with lowercase
    'subject-case': [2, 'always', 'lower-case'],
    // Header max length
    'header-max-length': [2, 'always', 100],
  },
};
