---
type: Decision
title: PHP Conventions
paths:
  - "**/*.php"
  - "**/composer.json"
  - "crates/*-php/**"
  - "packages/php/**"
x-ai-rulez:
  kind: rule
  id: php
  metadata:
    priority: high
---

- PHP 8.2+, `declare(strict_types=1)`, typed and readonly properties, enums, PSR-4 autoloading.
- PSR-12 formatting; PHPStan at max level; PHPUnit; Composer with a committed `composer.lock` and `composer audit`.
- No `@` suppression, `eval()`, `extract()` or dynamic properties.
- ext-php-rs bindings (`crates/*-php`): `#[php_class]`/`#[php_impl]`/`#[php_function]`, `PhpResult<T>`, map errors to specific PHP exceptions, mind reference counting in wrapped structs, no panics.
