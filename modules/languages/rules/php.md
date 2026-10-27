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
- Lint with mago through `poly lint` (`[lint.php.mago]` in poly.toml); PHPUnit; Composer with a committed `composer.lock`.
- No `@` suppression, `eval()`, `extract()` or dynamic properties.
