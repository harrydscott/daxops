/* DaxOps Web App — Alpine.js Application */

function daxops() {
    return {
        // Navigation
        screen: 'dashboard',
        loading: false,
        error: null,

        // Settings
        modelPath: null,
        modelLoaded: false,
        browsePath: null,
        browseEntries: [],
        browseParent: null,
        browseCurrent: '',

        // Dashboard data
        info: null,
        scoreData: null,
        checkData: null,

        // Findings filters
        filterSeverity: '',
        filterRule: '',
        filterTable: '',
        filterSearch: '',

        async init() {
            await this.loadSettings();
            if (this.modelPath) {
                await this.fullScan();
            }
        },

        // --- API calls ---
        async api(url, opts = {}) {
            try {
                const res = await fetch(url, opts);
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.detail || `HTTP ${res.status}`);
                }
                return await res.json();
            } catch (e) {
                this.error = e.message;
                throw e;
            }
        },

        async loadSettings() {
            try {
                const data = await this.api('/api/settings');
                this.modelPath = data.model_path;
                this.modelLoaded = data.model_loaded;
            } catch (e) { /* ignore on initial load */ }
        },

        async fullScan() {
            this.loading = true;
            this.error = null;
            try {
                await this.api('/api/scan', { method: 'POST' });
                await Promise.all([
                    this.loadInfo(),
                    this.loadScore(),
                    this.loadCheck(),
                ]);
                this.modelLoaded = true;
            } catch (e) {
                this.error = e.message;
            }
            this.loading = false;
        },

        async loadInfo() {
            this.info = await this.api('/api/info');
        },

        async loadScore() {
            this.scoreData = await this.api('/api/score');
        },

        async loadCheck() {
            this.checkData = await this.api('/api/check');
        },

        async rescan() {
            await this.fullScan();
        },

        async setModelPath(path) {
            this.loading = true;
            this.error = null;
            try {
                await this.api('/api/settings/model-path', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_path: path }),
                });
                this.modelPath = path;
                await this.fullScan();
                this.screen = 'dashboard';
            } catch (e) {
                this.error = e.message;
            }
            this.loading = false;
        },

        async browse(path) {
            try {
                const url = path ? `/api/browse?path=${encodeURIComponent(path)}` : '/api/browse';
                const data = await this.api(url);
                this.browseEntries = data.entries;
                this.browseParent = data.parent;
                this.browseCurrent = data.current;
            } catch (e) {
                this.error = e.message;
            }
        },

        async openSettings() {
            this.screen = 'settings';
            await this.browse(this.modelPath || null);
        },

        // --- Computed / helpers ---
        get tier() {
            return this.scoreData?.summary?.tier || 'none';
        },

        get tierLabel() {
            const t = this.tier;
            return t.charAt(0).toUpperCase() + t.slice(1);
        },

        get filteredFindings() {
            if (!this.checkData) return [];
            let findings = this.checkData.findings;

            if (this.filterSeverity) {
                findings = findings.filter(f => f.severity === this.filterSeverity);
            }
            if (this.filterRule) {
                findings = findings.filter(f => f.rule === this.filterRule);
            }
            if (this.filterTable) {
                findings = findings.filter(f => f.object_path.startsWith(this.filterTable));
            }
            if (this.filterSearch) {
                const term = this.filterSearch.toLowerCase();
                findings = findings.filter(f =>
                    f.message.toLowerCase().includes(term) ||
                    f.object_path.toLowerCase().includes(term)
                );
            }
            return findings;
        },

        get uniqueRules() {
            if (!this.checkData) return [];
            return [...new Set(this.checkData.findings.map(f => f.rule))].sort();
        },

        get uniqueTables() {
            if (!this.checkData) return [];
            const tables = this.checkData.findings.map(f => f.object_path.split('.')[0]);
            return [...new Set(tables)].sort();
        },

        sevClass(sev) {
            return {
                'ERROR': 'sev-icon-error',
                'WARNING': 'sev-icon-warning',
                'INFO': 'sev-icon-info',
            }[sev] || '';
        },

        sevIcon(sev) {
            return { 'ERROR': 'X', 'WARNING': '!', 'INFO': 'i' }[sev] || '?';
        },

        chipClass(sev) {
            return {
                'ERROR': 'chip-error',
                'WARNING': 'chip-warning',
                'INFO': 'chip-info',
            }[sev] || '';
        },

        clearFilters() {
            this.filterSeverity = '';
            this.filterRule = '';
            this.filterTable = '';
            this.filterSearch = '';
        },
    };
}
