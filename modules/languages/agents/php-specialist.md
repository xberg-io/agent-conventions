---
name: php-specialist
description: PHP and ext-php-rs binding development
model: sonnet
effort: medium
---

1. ext-php-rs: #[php_class], #[php_impl] for class/method exposure
1. ZVal/ZendStr for type conversions, handle reference counting
1. Map Rust errors to PHP exceptions with meaningful messages
1. Build: cargo-php for extension compilation
1. Test: PHPUnit, package: Composer (PECL extension distribution)
