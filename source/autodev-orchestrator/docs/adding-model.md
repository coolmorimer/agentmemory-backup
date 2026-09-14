# Adding a model

Add the model to `config/models.yaml` and its runtime `ModelProfile`. Declare provider, billing mode,
locality, private-code permission, capabilities, context limit, expected latency, quality/reliability,
and task-specific scores. A model without explicit metadata should not be selected.

Run router tests for public, private, and local-only tasks; test required tools/vision/structured output,
zero paid budget, cooldown, and explicit override. Observe real outcomes through model usage and the
dashboard before changing default weights. Keep prompt version in every recorded provider call.
