/* DaxOps Web App — Alpine.js Application */

function daxops() {
    return {
        // Navigation
        screen: 'dashboard',
        loading: false,
        error: null,
        toast: null,

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

        // Fix workflow
        fixPreview: null,
        fixLoading: false,
        showFixModal: false,
        fixSelected: [],  // indices of selected fixable items

        // Settings: rule toggles and thresholds
        settingsConfig: null,
        allRules: [
            'NAMING_CONVENTION', 'MISSING_DESCRIPTION', 'HIDDEN_KEYS',
            'MISSING_FORMAT', 'UNUSED_COLUMNS', 'DAX_COMPLEXITY',
            'MISSING_DATE_TABLE', 'BIDIRECTIONAL_RELATIONSHIP',
            'MISSING_DISPLAY_FOLDER', 'COLUMN_COUNT',
        ],
        excludedRules: [],
        thresholds: { bronze_min: 10, silver_min: 10, gold_min: 8 },

        // Score detail
        scoreDetailOpen: { Bronze: true, Silver: false, Gold: false },

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

        showToast(msg) {
            this.toast = msg;
            setTimeout(() => { this.toast = null; }, 4000);
        },

        async loadSettings() {
            try {
                const data = await this.api('/api/settings');
                this.modelPath = data.model_path;
                this.modelLoaded = data.model_loaded;
                if (data.exclude_rules) this.excludedRules = data.exclude_rules;
                if (data.thresholds) {
                    this.thresholds = data.thresholds;
                }
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

        // --- Fix workflow ---
        async openFixPreview() {
            this.fixLoading = true;
            this.error = null;
            try {
                this.fixPreview = await this.api('/api/fix/preview');
                this.fixSelected = this.fixPreview.fixable.map((_, i) => i);
                this.showFixModal = true;
            } catch (e) {
                this.error = e.message;
            }
            this.fixLoading = false;
        },

        toggleFixItem(idx) {
            const pos = this.fixSelected.indexOf(idx);
            if (pos >= 0) {
                this.fixSelected.splice(pos, 1);
            } else {
                this.fixSelected.push(idx);
            }
        },

        isFixSelected(idx) {
            return this.fixSelected.includes(idx);
        },

        async applyFixes() {
            this.fixLoading = true;
            this.error = null;
            try {
                const data = await this.api('/api/fix/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ selected: this.fixSelected }),
                });
                this.showFixModal = false;
                this.fixPreview = null;
                this.showToast(data.message);
                await this.fullScan();
            } catch (e) {
                this.error = e.message;
            }
            this.fixLoading = false;
        },

        async undoLastChange() {
            this.loading = true;
            this.error = null;
            try {
                const data = await this.api('/api/fix/undo', { method: 'POST' });
                this.showToast(data.message);
                await this.fullScan();
            } catch (e) {
                // Don't show error for "no backups" — just a toast
                if (e.message.includes('No backups')) {
                    this.showToast('No backups available to restore.');
                    this.error = null;
                }
            }
            this.loading = false;
        },

        // --- Settings: rule toggles & thresholds ---
        isRuleEnabled(rule) {
            return !this.excludedRules.includes(rule);
        },

        toggleRule(rule) {
            const idx = this.excludedRules.indexOf(rule);
            if (idx >= 0) {
                this.excludedRules.splice(idx, 1);
            } else {
                this.excludedRules.push(rule);
            }
        },

        async saveSettings() {
            this.error = null;
            try {
                await this.api('/api/settings/rules', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        exclude_rules: this.excludedRules,
                        thresholds: this.thresholds,
                    }),
                });
                this.showToast('Settings saved.');
                if (this.modelLoaded) await this.fullScan();
            } catch (e) {
                this.error = e.message;
            }
        },

        // --- Score detail ---
        toggleScoreDetail(tier) {
            this.scoreDetailOpen[tier] = !this.scoreDetailOpen[tier];
        },

        criterionTip(criterion) {
            if (criterion.score >= criterion.max_score) return 'Fully achieved!';
            if (criterion.score > 0) return 'Partially achieved. Review details to improve.';
            return 'Not yet achieved. Follow the recommendation to improve.';
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

        get fixableFindings() {
            const fixableRules = new Set(['NAMING_CONVENTION', 'HIDDEN_KEYS']);
            return this.filteredFindings.filter(f => fixableRules.has(f.rule));
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
