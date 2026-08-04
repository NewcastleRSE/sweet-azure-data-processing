python3 -m venv .venv
source .venv/bin/activate
python inspect_schema.py
deactivate


npm run strapi console
// Run this inside `npm run strapi console`
const entries = await strapi.documents('api::page.page').findMany({ publicationState: 'preview' });
for (const entry of entries) {
  await strapi.documents('api::page.page').delete({ documentId: entry.documentId });
}
console.log(`Deleted ${entries.length} pages.`);