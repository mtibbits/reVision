---
title: Adding two numbers
summary: One helper function, one call, one print.
file: src/hello.c
start: add-fn
---
# Adding two numbers

This tiny program has two functions. The [helper](@add-fn) takes two integers and
[returns their sum](@add-expr). The [entry point](@main-fn) [calls it once](@call-site)
and prints the result.

![Call flow](diagrams/flow.dot)

Real SIMD code would replace the single addition with something like `_mm256_fmadd_ps`,
which is why every kernel lesson links intrinsic names to the vendor's reference.

```quiz
questions:
  - q: What does add(2, 3) return?
    choices: ["5", "6", "23"]
    answer: 0
  - q: Which function is the program's entry point?
    choices: [add, main, printf]
    answer: 1
```
