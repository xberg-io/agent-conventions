---
type: Decision
title: PHP Binding Conventions
paths:
  - "crates/*-php/**"
  - "packages/php/**"
x-ai-rulez:
  kind: rule
  id: php-bindings
  metadata:
    priority: high
---

- ext-php-rs (`crates/*-php`): `#[php_class]`/`#[php_impl]`/`#[php_function]`, `PhpResult<T>`, map errors to specific PHP exceptions, mind reference counting in wrapped structs, no panics.
