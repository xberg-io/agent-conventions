---
type: Decision
title: PHP Conventions
paths:
  - "**/*.php"
  - "**/composer.json"
x-ai-rulez:
  kind: rule
  id: php
  metadata:
    priority: high
---

- PHP 8.2+, `declare(strict_types=1)`, typed and readonly properties, enums, PSR-4 autoloading.
- PSR-12 formatting; PHPStan at max level; PHPUnit; Composer with a committed `composer.lock` and `composer audit`.
- No `@` suppression, `eval()`, `extract()` or dynamic properties.
