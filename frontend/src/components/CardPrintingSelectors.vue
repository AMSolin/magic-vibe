<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import Select from 'primevue/select';

import type { CardPrinting } from '@/shared/api';

type SetOption = {
  code: string;
  keyrune: string;
  name: string;
  releaseDate: number;
};

export type CardPrintingSelection = {
  printing: CardPrinting | null;
  setCode: string;
  setName: string;
  languageCode: string;
  language: string;
  collectorNumber: string;
  finishId: number | null;
  finish: string;
};

const props = withDefaults(
  defineProps<{
    printings: CardPrinting[];
    preferredLanguageCode?: string;
    initialPrintingId?: number | null;
    initialLanguageCode?: string;
    initialFinishId?: number | null;
  }>(),
  {
    preferredLanguageCode: '',
    initialPrintingId: null,
    initialLanguageCode: '',
    initialFinishId: null,
  },
);
const emit = defineEmits<{
  selectionChange: [selection: CardPrintingSelection];
}>();

const selectedSetCode = ref('');
const languageCode = ref('');
const preferredLanguageCode = ref('');
const cardNumber = ref('');
const finishId = ref<number | null>(null);

const sets = computed<SetOption[]>(() => {
  const uniqueSets = new Map<string, SetOption>();
  for (const printing of props.printings) {
    if (!uniqueSets.has(printing.set_code)) {
      uniqueSets.set(printing.set_code, {
        code: printing.set_code,
        keyrune: printing.keyrune_code.toLocaleLowerCase(),
        name: printing.set_name,
        releaseDate: printing.release_date,
      });
    }
  }
  return [...uniqueSets.values()].sort((left, right) => right.releaseDate - left.releaseDate);
});
const selectedSet = computed(() => sets.value.find((set) => set.code === selectedSetCode.value));
const setPrintings = computed(() =>
  props.printings.filter((printing) => printing.set_code === selectedSetCode.value),
);
const languages = computed(() => {
  const uniqueLanguages = new Map<string, string>();
  for (const printing of setPrintings.value) {
    uniqueLanguages.set(printing.language_code, printing.language);
    for (const localization of printing.localizations) {
      uniqueLanguages.set(localization.code, localization.name);
    }
  }
  return [...uniqueLanguages.entries()].map(([code, name]) => ({ code, name }));
});
const languagePrintings = computed(() =>
  setPrintings.value.filter(
    (printing) =>
      printing.language_code === languageCode.value ||
      printing.localizations.some((localization) => localization.code === languageCode.value),
  ),
);
const numbers = computed(() => [
  ...new Set(languagePrintings.value.map((printing) => printing.collector_number)),
]);
const selectedPrinting = computed(
  () =>
    languagePrintings.value.find(
      (printing) =>
        printing.collector_number === cardNumber.value && printing.language_code === languageCode.value,
    ) ??
    languagePrintings.value.find((printing) => printing.collector_number === cardNumber.value) ??
    null,
);
const finishes = computed(() => selectedPrinting.value?.finishes ?? []);

function selectSet(set: SetOption): void {
  selectedSetCode.value = set.code;
  const availableLanguages = new Set(
    props.printings.flatMap((printing) =>
      printing.set_code === set.code
        ? [printing.language_code, ...printing.localizations.map((localization) => localization.code)]
        : [],
    ),
  );
  languageCode.value =
    (preferredLanguageCode.value && availableLanguages.has(preferredLanguageCode.value)
      ? preferredLanguageCode.value
      : languages.value[0]?.code) ?? '';
  cardNumber.value = numbers.value[0] ?? '';
  finishId.value = finishes.value[0]?.id ?? null;
}

function selectLanguage(value: string): void {
  preferredLanguageCode.value = value;
  languageCode.value = value;
}

function initialize(): void {
  preferredLanguageCode.value = props.preferredLanguageCode || props.initialLanguageCode;
  const initialPrinting = props.printings.find((printing) => printing.id === props.initialPrintingId);
  if (initialPrinting) {
    selectedSetCode.value = initialPrinting.set_code;
    languageCode.value = props.initialLanguageCode || initialPrinting.language_code;
    cardNumber.value = initialPrinting.collector_number;
    finishId.value = props.initialFinishId ?? initialPrinting.finishes[0]?.id ?? null;
    return;
  }
  const firstSet =
    (preferredLanguageCode.value
      ? sets.value.find((set) =>
          props.printings.some(
            (printing) =>
              printing.set_code === set.code &&
              (printing.language_code === preferredLanguageCode.value ||
                printing.localizations.some(
                  (localization) => localization.code === preferredLanguageCode.value,
                )),
          ),
        )
      : undefined) ?? sets.value[0];
  if (firstSet) {
    selectSet(firstSet);
  }
}

watch(
  () => props.printings,
  initialize,
  { immediate: true },
);

watch(languageCode, () => {
  cardNumber.value = numbers.value.includes(cardNumber.value) ? cardNumber.value : (numbers.value[0] ?? '');
});

watch(
  [selectedPrinting, languageCode, finishId],
  () => {
    finishId.value = finishes.value.some((finish) => finish.id === finishId.value)
      ? finishId.value
      : (finishes.value[0]?.id ?? null);
    emit('selectionChange', {
      printing: selectedPrinting.value,
      setCode: selectedSetCode.value,
      setName: selectedSet.value?.name ?? '',
      languageCode: languageCode.value,
      language: languages.value.find((language) => language.code === languageCode.value)?.name ?? '',
      collectorNumber: cardNumber.value,
      finishId: finishId.value,
      finish: finishes.value.find((finish) => finish.id === finishId.value)?.name ?? '',
    });
  },
  { immediate: true },
);
</script>

<template>
  <div class="card-attributes">
    <div class="field">
      <span>Set</span>
      <div class="set-icon-grid">
        <button
          v-for="set in sets"
          :key="set.code"
          type="button"
          :aria-label="set.name"
          :class="{ selected: selectedSetCode === set.code }"
          @click="selectSet(set)"
        >
          <i :class="`ss ss-${set.keyrune} ss-2x`" />
        </button>
      </div>
      <strong class="selected-set-name">{{ selectedSet?.name }}</strong>
    </div>
    <label class="field">
      <span>Language</span>
      <Select
        :model-value="languageCode"
        :options="languages"
        option-label="name"
        option-value="code"
        @update:model-value="selectLanguage"
      />
    </label>
    <div class="field">
      <span>Card number</span>
      <div class="number-toggle-group">
        <button
          v-for="number in numbers"
          :key="number"
          type="button"
          :class="{ selected: cardNumber === number }"
          @click="cardNumber = number"
        >
          {{ number }}
        </button>
      </div>
    </div>
    <label class="field">
      <span>Finish</span>
      <Select v-model="finishId" :options="finishes" option-label="name" option-value="id" />
    </label>
  </div>
</template>
