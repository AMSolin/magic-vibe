<script setup lang="ts">
import Paginator from 'primevue/paginator';

type PageEvent = {
  first: number;
  rows: number;
  page?: number;
  pageCount?: number;
};

withDefaults(
  defineProps<{
    first: number;
    rows: number;
    totalRecords: number;
    rowsPerPageOptions?: number[];
  }>(),
  {
    rowsPerPageOptions: () => [25, 50, 100, 200],
  },
);

defineEmits<{
  page: [event: PageEvent];
}>();
</script>

<template>
  <Paginator
    :first="first"
    :rows="rows"
    :total-records="totalRecords"
    :rows-per-page-options="rowsPerPageOptions"
    template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink RowsPerPageDropdown CurrentPageReport"
    current-page-report-template="{first}-{last} of {totalRecords}"
    @page="$emit('page', $event)"
  />
</template>
