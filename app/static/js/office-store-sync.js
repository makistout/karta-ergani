Object.assign(window.Office, {
  async recordStoreSync(kind) {
    try {
      const res = await fetch("/api/store/record-sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind }),
        cache: "no-store",
      });
      this.invalidateActiveStoreCache();
      return await this.parseJson(res);
    } catch (e) {
      return { success: false, error: String(e) };
    }
  },

  async refreshActiveStoreSyncMeta(elId, kind, store) {
    try {
      if (store) {
        this.updateSyncMetaLine(elId, store, kind);
        return store;
      }
      const data = await this.fetchActiveStore();
      if (data.store) {
        this.updateSyncMetaLine(elId, data.store, kind);
      }
      return data.store || null;
    } catch {
      return null;
    }
  },

  formatSyncedAt(iso) {
    if (!iso) return "—";
    return String(iso).replace("T", " ").slice(0, 16);
  },
});
