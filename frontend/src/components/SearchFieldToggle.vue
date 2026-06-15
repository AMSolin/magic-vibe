<script setup lang="ts">
type SearchFieldOption<T extends string> = {
  label: string;
  value: T;
};

defineProps<{
  modelValue: string;
  options: readonly SearchFieldOption<string>[];
  ariaLabel?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();
</script>

<template>
  <div class="search-field-toggle" :aria-label="ariaLabel ?? 'Search field'">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :class="{ selected: modelValue === option.value }"
      :aria-pressed="modelValue === option.value"
      :title="`Search by ${option.label.toLowerCase()}`"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>
