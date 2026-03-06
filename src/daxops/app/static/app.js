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

        // AI Description Editor
        aiSettings: null,
        aiProvider: 'openai',
        aiModel: 'gpt-4o',
        aiAzureEndpoint: '',
        aiApiKey: '',
        aiTestResult: null,
        aiTesting: false,
        descObjects: [],
        descGenerating: false,
        descProgress: { current: 0, total: 0 },
        descFilter: '',  // filter by type: '', 'measure', 'column', 'table'
        descStatusFilter: '',  // filter by status
        descSearch: '',

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
            await Promise.all([
                this.browse(this.modelPath || null),
                this.loadAISettings(),
            ]);
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

        // --- AI Provider Settings ---
        async loadAISettings() {
            try {
                const data = await this.api('/api/ai/settings');
                this.aiSettings = data;
                this.aiProvider = data.provider;
                this.aiModel = data.llm_model;
                this.aiAzureEndpoint = data.azure_endpoint || '';
            } catch (e) { /* ignore */ }
        },

        async saveAISettings() {
            this.error = null;
            try {
                const data = await this.api('/api/ai/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        provider: this.aiProvider,
                        llm_model: this.aiModel,
                        azure_endpoint: this.aiAzureEndpoint || null,
                    }),
                });
                this.aiSettings = data;
                // Save API key if provided
                if (this.aiApiKey) {
                    await this.api('/api/ai/key', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            provider: this.aiProvider,
                            api_key: this.aiApiKey,
                        }),
                    });
                    this.aiApiKey = '';  // Clear from UI
                    await this.loadAISettings();
                }
                this.showToast('AI settings saved.');
            } catch (e) {
                this.error = e.message;
            }
        },

        async testAIConnection() {
            this.aiTesting = true;
            this.aiTestResult = null;
            try {
                // Save settings first
                await this.saveAISettings();
                const data = await this.api('/api/ai/test', { method: 'POST' });
                this.aiTestResult = data;
            } catch (e) {
                this.aiTestResult = { success: false, message: e.message };
            }
            this.aiTesting = false;
        },

        // --- AI Description Editor ---
        async openDescribeScreen() {
            this.screen = 'describe';
            await this.loadUndocumented();
        },

        async loadUndocumented() {
            this.error = null;
            try {
                const data = await this.api('/api/document/undocumented');
                this.descObjects = data.objects;
            } catch (e) {
                this.error = e.message;
            }
        },

        get filteredDescObjects() {
            let objs = this.descObjects;
            if (this.descFilter) {
                objs = objs.filter(o => o.object_type === this.descFilter);
            }
            if (this.descStatusFilter) {
                objs = objs.filter(o => o.status === this.descStatusFilter);
            }
            if (this.descSearch) {
                const term = this.descSearch.toLowerCase();
                objs = objs.filter(o =>
                    o.name.toLowerCase().includes(term) ||
                    o.object_path.toLowerCase().includes(term) ||
                    (o.description || '').toLowerCase().includes(term)
                );
            }
            return objs;
        },

        get descStats() {
            const total = this.descObjects.length;
            const generated = this.descObjects.filter(o => o.status === 'generated').length;
            const edited = this.descObjects.filter(o => o.status === 'edited').length;
            const approved = this.descObjects.filter(o => o.status === 'approved').length;
            const written = this.descObjects.filter(o => o.status === 'written').length;
            const pending = this.descObjects.filter(o => o.status === 'not_generated').length;
            return { total, generated, edited, approved, written, pending };
        },

        async generateDescriptions(paths) {
            this.descGenerating = true;
            this.descProgress = { current: 0, total: paths ? paths.length : this.descObjects.length };
            this.error = null;
            try {
                // Try WebSocket first for real-time progress
                const wsUrl = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/progress`;
                const ws = new WebSocket(wsUrl);
                const self = this;
                let resolved = false;

                await new Promise((resolve, reject) => {
                    ws.onopen = () => {
                        ws.send(JSON.stringify({
                            action: 'generate',
                            object_paths: paths || null,
                        }));
                    };
                    ws.onmessage = (e) => {
                        const msg = JSON.parse(e.data);
                        if (msg.type === 'start') {
                            self.descProgress.total = msg.total;
                        } else if (msg.type === 'progress') {
                            self.descProgress.current = msg.current;
                            // Update the object in our list
                            const idx = self.descObjects.findIndex(o => o.object_path === msg.item.object_path);
                            if (idx >= 0) {
                                self.descObjects[idx] = msg.item;
                            }
                        } else if (msg.type === 'complete') {
                            resolved = true;
                            ws.close();
                            resolve();
                        }
                    };
                    ws.onerror = () => {
                        // Fallback to HTTP if WebSocket fails
                        if (!resolved) {
                            ws.close();
                            self._generateViaHttp(paths).then(resolve).catch(reject);
                        }
                    };
                    ws.onclose = () => {
                        if (!resolved) resolve();
                    };
                });

                await this.loadUndocumented();
                this.showToast(`Generated ${this.descProgress.current} descriptions.`);
            } catch (e) {
                this.error = e.message;
            }
            this.descGenerating = false;
        },

        async _generateViaHttp(paths) {
            const data = await this.api('/api/document/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ object_paths: paths || null }),
            });
            this.descProgress.current = data.total;
        },

        async generateAll() {
            await this.generateDescriptions(null);
        },

        async generateSelected(paths) {
            await this.generateDescriptions(paths);
        },

        async regenerateOne(path) {
            await this.generateDescriptions([path]);
        },

        async updateDescription(obj, newDesc) {
            try {
                const data = await this.api('/api/document/description', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        object_path: obj.object_path,
                        description: newDesc,
                        status: 'edited',
                    }),
                });
                const idx = this.descObjects.findIndex(o => o.object_path === obj.object_path);
                if (idx >= 0) this.descObjects[idx] = data;
            } catch (e) {
                this.error = e.message;
            }
        },

        async approveOne(path) {
            try {
                await this.api('/api/document/approve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ object_paths: [path] }),
                });
                const idx = this.descObjects.findIndex(o => o.object_path === path);
                if (idx >= 0) this.descObjects[idx].status = 'approved';
            } catch (e) {
                this.error = e.message;
            }
        },

        async approveAll() {
            const paths = this.descObjects
                .filter(o => o.status === 'generated' || o.status === 'edited')
                .map(o => o.object_path);
            if (!paths.length) return;
            try {
                await this.api('/api/document/approve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ object_paths: paths }),
                });
                for (const p of paths) {
                    const idx = this.descObjects.findIndex(o => o.object_path === p);
                    if (idx >= 0) this.descObjects[idx].status = 'approved';
                }
                this.showToast(`Approved ${paths.length} descriptions.`);
            } catch (e) {
                this.error = e.message;
            }
        },

        async writeApproved() {
            this.loading = true;
            this.error = null;
            try {
                const data = await this.api('/api/document/write', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({}),
                });
                this.showToast(data.message);
                await this.loadUndocumented();
                await this.fullScan();
            } catch (e) {
                this.error = e.message;
            }
            this.loading = false;
        },

        descStatusLabel(status) {
            return {
                'not_generated': 'Pending',
                'generated': 'Generated',
                'edited': 'Edited',
                'approved': 'Approved',
                'written': 'Written',
            }[status] || status;
        },

        descStatusClass(status) {
            return {
                'not_generated': 'desc-pending',
                'generated': 'desc-generated',
                'edited': 'desc-edited',
                'approved': 'desc-approved',
                'written': 'desc-written',
            }[status] || '';
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
