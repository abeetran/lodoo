/** @odoo-module **/
import { Component, useState, onWillStart, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

function parseSuggestedAction(actionParam) {
    const tokens = actionParam.split(/\|+/).map((t) => t.trim()).filter(Boolean);
    let actionStr = tokens.length > 0 ? tokens[0] : actionParam;
    const options = {};
    for (const token of tokens.slice(1)) {
        if (token === "NEW") {
            options.viewType = "form";
            continue;
        }
        if (token.startsWith("OD_ACTION:")) {
            actionStr = token.substring(10).trim();
            continue;
        }
        if (token.startsWith("DOMAIN:")) {
            try {
                options.domain = JSON.parse(token.substring(7));
            } catch (e) {
                console.error("Lỗi parse domain:", e);
            }
        }
    }
    if (actionStr.startsWith("OD_ACTION:")) {
        actionStr = actionStr.substring(10).trim();
    }
    return { actionStr, options };
}

function getDateGroup(dateStr) {
    const now = new Date();
    const d = new Date(dateStr);
    const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "today";
    if (diffDays <= 7) return "recent";
    return "older";
}

export class AiChatFloatingWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.router = useService("router");
        this.menuService = useService("menu");
        this.userService = useService("user");

        this.state = useState({
            isOpen: false, messages: [], inputText: "", isLoading: false,
            currentModuleName: "", activeChatId: null, userInitial: "U",
        });

        this.moduleChatMemory = {};
        this.chatEndRef = useRef("chatEndMini");

        onWillStart(() => {
            const userName = this.userService.name || "Người dùng";
            this.state.userInitial = userName.charAt(0).toUpperCase();
        });

        useEffect(() => {
            if (this.state.isOpen && this.chatEndRef.el) { this.chatEndRef.el.scrollIntoView({ behavior: "smooth" }); }
        }, () => [this.state.messages.length, this.state.isLoading, this.state.isOpen]);
    }

    toggleChat() {
        this.state.isOpen = !this.state.isOpen;
        if (this.state.isOpen) {
            const currentApp = this.menuService.getCurrentApp();
            const moduleName = currentApp ? currentApp.name : "Hệ thống chung";
            const currentModKey = currentApp ? currentApp.xmlid : 'general';

            if (this.moduleChatMemory[currentModKey]) {
                const memo = this.moduleChatMemory[currentModKey];
                this.state.messages = memo.messages;
                this.state.activeChatId = memo.chatId;
                this.state.currentModuleName = moduleName;
            } else {
                this.state.currentModuleName = moduleName;
                this.state.activeChatId = null;
                this.state.messages = [{ role: "ai", content: `Bạn cần gì ở ${moduleName} này!` }];
                this._saveModuleMemory(currentModKey);
            }
        }
    }

    async sendMessage() {
        const text = this.state.inputText.trim();
        if (!text || this.state.isLoading) return;

        this.state.messages.push({ role: "user", content: text });
        this.state.inputText = "";
        this.state.isLoading = true;

        try {
            const promptWithContext = `[Ngữ cảnh: Người dùng đang ở module ${this.state.currentModuleName} của Odoo] ${text}`;
            const res = await this.orm.call("odoo.ai.chat", "send_message_from_ui", [promptWithContext, [], this.state.activeChatId || null]);

            if (res.chat_id && !this.state.activeChatId) this.state.activeChatId = res.chat_id;

            const msg = { role: "ai", content: res.answer };
            if (res.suggested_action) msg.suggested_action = res.suggested_action;
            this.state.messages.push(msg);

            const currentApp = this.menuService.getCurrentApp();
            const currentModKey = currentApp ? currentApp.xmlid : 'general';
            this._saveModuleMemory(currentModKey);

        } catch (error) { this.state.messages.push({ role: "ai", content: _t("Lỗi kết nối đến máy chủ AI.") });
        } finally { this.state.isLoading = false; }
    }

    _saveModuleMemory(modKey) { this.moduleChatMemory[modKey] = { chatId: this.state.activeChatId, messages: [...this.state.messages] }; }

    async openSuggestedAction(actionParam) {
        try {
            const parsed = parseSuggestedAction(actionParam || "");
            let actionRef = parsed.actionStr;
            let domainStr = false;
            let viewType = false;

            if (parsed.options.domain) domainStr = JSON.stringify(parsed.options.domain);
            if (parsed.options.viewType === "form") viewType = "form";

            let actionObj = await this.orm.call("odoo.ai.chat", "get_action_data", [actionRef, domainStr, viewType]);
            
            if (actionObj) {
                await this.orm.call("odoo.ai.chat", "log_user_behavior", ["module_visit", String(actionObj.id), ""]);
                await this.actionService.doAction(actionObj);
            } else {
                let finalAction = actionRef;
                if (actionRef.includes(",")) finalAction = parseInt(actionRef.split(",")[1]);
                else if (!isNaN(actionRef)) finalAction = parseInt(actionRef);
                
                await this.orm.call("odoo.ai.chat", "log_user_behavior", ["module_visit", String(finalAction), ""]);
                await this.actionService.doAction(finalAction, parsed.options);
            }
        } catch (e) { console.error("Lỗi mở màn hình:", e); }
    }

    onKeydown(ev) { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.sendMessage(); } }
}
AiChatFloatingWidget.template = "odoo_ai_assistant.AiChatFloatingWidgetTemplate";
registry.category("main_components").add("odoo_ai_assistant.AiChatFloatingWidget", { Component: AiChatFloatingWidget });


export class AiChatWindow extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.userService = useService("user");

        useEffect(() => {
            document.body.classList.add("hide-ai-bubble");
            return () => { document.body.classList.remove("hide-ai-bubble"); };
        }, () => []);

        this.state = useState({
            messages: [], inputText: "", isLoading: false, activeChatId: null,
            chatHistory: [], searchQuery: "", isDarkTheme: false,
            userName: "", userInitial: "U", attachments: [],
            suggestions: { modules: [], queries: [], related: [] }
        });

        this.chatEndRef = useRef("chatEnd");
        this.chatInputRef = useRef("chatInput");
        this.fileInputRef = useRef("fileInput");

        onWillStart(async () => {
            const savedTheme = localStorage.getItem("odoo_ai_theme");
            if (savedTheme !== null) this.state.isDarkTheme = savedTheme !== "light";

            this.state.userName = this.userService.name || "Người dùng";
            this.state.userInitial = this.state.userName.charAt(0).toUpperCase();

            await this._loadSidebarHistory();
            this.startNewChat();
            const data = await this.orm.call("odoo.ai.chat", "get_personalized_suggestions", []);
            this.state.suggestions = data;

            await this.orm.call("odoo.ai.chat", "log_user_behavior", ["module_visit", "odoo_ai_assistant.action_ai_chat_client", "AI Assistant"]);
        });

        useEffect(() => {
            if (this.chatEndRef.el) { this.chatEndRef.el.scrollIntoView({ behavior: "smooth" }); }
        }, () => [this.state.messages.length, this.state.isLoading]);
    }
    
    async openModule(actionXmlId) { await this.actionService.doAction(actionXmlId); }
    triggerFileInput() { if (this.fileInputRef.el) this.fileInputRef.el.click(); }

    async onFileChange(ev) {
        const files = ev.target.files;
        if (!files || files.length === 0) return;
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const base64Data = await this._toBase64(file);
            this.state.attachments.push({ name: file.name, type: file.type, data: base64Data.split(",")[1] });
        }
        ev.target.value = "";
    }

    removeAttachment(fileName) { this.state.attachments = this.state.attachments.filter(f => f.name !== fileName); }

    _toBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result);
            reader.onerror = error => reject(error);
        });
    }

    async _loadSidebarHistory() {
        try {
            const records = await this.orm.searchRead(
                "odoo.ai.chat", [["user_id", "=", this.userService.userId]], ["id", "name", "write_date"],
                { order: "id desc", limit: 50 }
            );
            this.state.chatHistory = records;
        } catch (e) { this.state.chatHistory = []; }
    }

    get filteredHistory() {
        const q = this.state.searchQuery.trim().toLowerCase();
        if (!q) return this.state.chatHistory;
        return this.state.chatHistory.filter((c) => c.name.toLowerCase().includes(q));
    }

    get todayChats() { return this.filteredHistory.filter((c) => getDateGroup(c.write_date) === "today"); }
    get recentChats() { return this.filteredHistory.filter((c) => getDateGroup(c.write_date) === "recent"); }
    get olderChats() { return this.filteredHistory.filter((c) => getDateGroup(c.write_date) === "older"); }

    async loadChat(chatId) {
        this.state.activeChatId = chatId;
        this.state.isLoading = true;
        try {
            const historyJson = await this.orm.call("odoo.ai.chat", "get_chat_history", [chatId]);
            this.state.messages = historyJson || [];
        } catch (e) { this.state.messages = [{ role: "ai", content: _t("Không thể tải dữ liệu.") }]; } 
        finally { this.state.isLoading = false; }
    }

    toggleTheme() {
        this.state.isDarkTheme = !this.state.isDarkTheme;
        localStorage.setItem("odoo_ai_theme", this.state.isDarkTheme ? "dark" : "light");
    }

    startNewChat() {
        this.state.messages = [];
        this.state.activeChatId = null;
        this.state.inputText = "";
        setTimeout(() => { if (this.chatInputRef.el) this.chatInputRef.el.focus(); }, 50);
    }

    async deleteChat(chatId) {
        try {
            await this.orm.unlink("odoo.ai.chat", [chatId]);
            await this._loadSidebarHistory();
            if (this.state.activeChatId === chatId) { this.startNewChat(); }
        } catch (e) { console.error("Lỗi xóa chat:", e); }
    }

    useQuickPrompt(text) { this.state.inputText = text; this.sendMessage(); }
    onSearchInput(ev) { this.state.searchQuery = ev.target.value; }

    async sendMessage() {
        const text = this.state.inputText.trim();
        const files = [...this.state.attachments];
        if (!text && files.length === 0 || this.state.isLoading) return;

        let userContent = text;
        if (files.length > 0) userContent += `\n[Đã đính kèm ${files.length} tệp]`;

        this.state.messages.push({ role: "user", content: userContent });
        this.state.inputText = "";
        this.state.attachments = [];
        this.state.isLoading = true;

        try {
            const res = await this.orm.call("odoo.ai.chat", "send_message_from_ui", [], {
                question: text, attachments: files, chat_id: this.state.activeChatId || false
            });

            if (res.chat_id && !this.state.activeChatId) this.state.activeChatId = res.chat_id;

            const msg = { role: "ai", content: res.answer };
            if (res.suggested_action) msg.suggested_action = res.suggested_action;
            this.state.messages.push(msg);

            await this._loadSidebarHistory();
            if (text.length < 50) this.orm.call("odoo.ai.chat", "log_user_behavior", ["frequent_question", text]);
        } catch (error) { this.state.messages.push({ role: "ai", content: _t("Lỗi kết nối: Không thể kết nối đến máy chủ AI.") });
        } finally { this.state.isLoading = false; }
    }

    async openSuggestedAction(actionParam) {
        try {
            const parsed = parseSuggestedAction(actionParam || "");
            let actionRef = parsed.actionStr;
            let domainStr = false;
            let viewType = false;

            if (parsed.options.domain) domainStr = JSON.stringify(parsed.options.domain);
            if (parsed.options.viewType === "form") viewType = "form";

            let actionObj = await this.orm.call("odoo.ai.chat", "get_action_data", [actionRef, domainStr, viewType]);
            
            if (actionObj) {
                await this.orm.call("odoo.ai.chat", "log_user_behavior", ["module_visit", String(actionObj.id), ""]);
                await this.actionService.doAction(actionObj);
            } else {
                let finalAction = actionRef;
                if (actionRef.includes(",")) finalAction = parseInt(actionRef.split(",")[1]);
                else if (!isNaN(actionRef)) finalAction = parseInt(actionRef);
                
                await this.orm.call("odoo.ai.chat", "log_user_behavior", ["module_visit", String(finalAction), ""]);
                await this.actionService.doAction(finalAction, parsed.options);
            }
        } catch (e) { console.error("Lỗi mở màn hình:", e); }
    }

    onKeydown(ev) { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.sendMessage(); } }
}
AiChatWindow.template = "odoo_ai_assistant.AiChatWindowTemplate";
registry.category("actions").add("odoo_ai_assistant.AiChatClientAction", AiChatWindow);