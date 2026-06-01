<script setup lang="ts">
import { computed, onMounted } from 'vue';

import { loadScryfallSymbols, scryfallSymbols } from '@/shared/scryfallSymbols';

const props = defineProps<{
  text: string;
}>();

const pieces = computed(() =>
  props.text
    .split(/(\{[^}]+\})/g)
    .filter(Boolean)
    .map((text) => ({ text, symbol: scryfallSymbols.value[text] })),
);

onMounted(loadScryfallSymbols);
</script>

<template>
  <span class="scryfall-symbols-text">
    <template v-for="(piece, index) in pieces" :key="`${index}-${piece.text}`">
      <img
        v-if="piece.symbol"
        class="scryfall-symbol"
        :src="piece.symbol.image_url"
        :alt="piece.text"
        :title="piece.symbol.label"
      />
      <span v-else>{{ piece.text }}</span>
    </template>
  </span>
</template>
