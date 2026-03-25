/** @odoo-module **/
import { Component, useState, onWillStart, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

function getDateGroup(dateStr) {
    const now = new Date();
    const d = new Date(dateStr);
    const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "today";
    if (diffDays <= 7) return "recent";
    return "older";
}

// ==========================================================
// COMPONENT 1: BÓNG CHAT TRÔI NỔI (MINI)
// ==========================================================
export class AiChatFloatingWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.router = useService("router");
        this.menuService = useService("menu"); 
        this.userService = useService("user"); // ĐỂ LẤY TÊN USER

        this.state = useState({ 
            isOpen: false,
            messages: [],
            inputText: "",
            isLoading: false,
            currentModuleName: "",
            activeChatId: null,
            userInitial: "U", // Giá trị mặc định
        });
        
        // BỘ NHỚ ĐỆM: Nhớ ID luồng và Tin nhắn của từng Module
        this.moduleChatMemory = {}; 

        this.chatEndRef = useRef("chatEndMini");

        onWillStart(() => {
            // Lấy chữ cái đầu của User
            const userName = this.userService.name || "Người dùng";
            this.state.userInitial = userName.charAt(0).toUpperCase();
        });

        // 1. Tự động cuộn chat mini
        useEffect(() => {
            if (this.state.isOpen && this.chatEndRef.el) {
                this.chatEndRef.el.scrollIntoView({ behavior: "smooth" });
            }
        }, () => [this.state.messages.length, this.state.isLoading, this.state.isOpen]);
    }

    // ĐÓNG / MỞ MINI CHAT VÀ PHỤC HỒI NGỮ CẢNH CŨ
    toggleChat() {
        this.state.isOpen = !this.state.isOpen;
        
        if (this.state.isOpen) {
            const currentApp = this.menuService.getCurrentApp();
            const moduleName = currentApp ? currentApp.name : "Hệ thống chung";
            const currentModKey = currentApp ? currentApp.xmlid : 'general';
            
            // LOGIC MỚI: PHỤC HỒI HOẶC TẠO MỚI TIN NHẮN THEO MODULE
            // 1. Nếu quay lại Module cũ -> Moi trong bộ nhớ ra
            if (this.moduleChatMemory[currentModKey]) {
                const memo = this.moduleChatMemory[currentModKey];
                this.state.messages = memo.messages;
                this.state.activeChatId = memo.chatId;
                this.state.currentModuleName = moduleName;
            } 
            // 2. Nếu Module mới tinh hoặc chưa chat câu nào -> Tạo câu chào mới
            else {
                this.state.currentModuleName = moduleName;
                this.state.activeChatId = null; 
                this.state.messages = [{
                    role: "ai",
                    content: `Bạn cần gì ở module ${moduleName} này!`
                }];
                // Khởi tạo bộ nhớ cho Module này
                this._saveModuleMemory(currentModKey);
            }
        }
    }

    // GỬI TIN NHẮN (Gửi chat_id cũ nếu có)
    async sendMessage() {
        const text = this.state.inputText.trim();
        if (!text || this.state.isLoading) return;

        // Thêm tin nhắn User vào màn hình
        this.state.messages.push({ role: "user", content: text });
        this.state.inputText = "";
        this.state.isLoading = true;

        try {
            const promptWithContext = `[Ngữ cảnh: Người dùng đang ở module ${this.state.currentModuleName} của Odoo] ${text}`;
            
            // TRUYỀN ID CŨ (Nếu có) ĐỂ PYTHON LƯU NỐI TIẾP
            const res = await this.orm.call("odoo.ai.chat", "send_message_from_ui", [
                promptWithContext, 
                [], 
                this.state.activeChatId || null 
            ]);

            // Nếu là câu chat đầu, lấy lại ID luồng từ Python
            if (res.chat_id && !this.state.activeChatId) {
                this.state.activeChatId = res.chat_id;
            }

            // Thêm tin nhắn Bot vào màn hình
            const msg = { role: "ai", content: res.answer };
            if (res.suggested_action) msg.suggested_action = res.suggested_action;
            this.state.messages.push(msg);

            // CẬP NHẬT LẠI BỘ NHỚ PER MODULE
            const currentApp = this.menuService.getCurrentApp();
            const currentModKey = currentApp ? currentApp.xmlid : 'general';
            this._saveModuleMemory(currentModKey);

        } catch (error) {
            this.state.messages.push({
                role: "ai",
                content: _t("Lỗi kết nối đến máy chủ AI.")
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    // Hàm phụ trợ lưu dữ liệu vào bộ nhớ đệm
    _saveModuleMemory(modKey) {
        this.moduleChatMemory[modKey] = {
            chatId: this.state.activeChatId,
            messages: [...this.state.messages] // Copy mảng
        };
    }

    async openSuggestedAction(xmlId) {
        try { await this.actionService.doAction(xmlId); } 
        catch (error) { console.error("Lỗi mở báo cáo:", error); }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}
AiChatFloatingWidget.template = "odoo_ai_assistant.AiChatFloatingWidgetTemplate";
registry.category("main_components").add("odoo_ai_assistant.AiChatFloatingWidget", { Component: AiChatFloatingWidget });


// ==========================================================
// COMPONENT 2: MÀN HÌNH CHÍNH CHATGPT STYLE
// ==========================================================
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
            messages: [],           
            inputText: "",
            isLoading: false,
            activeChatId: null,    
            chatHistory: [],        
            searchQuery: "",        
            isDarkTheme: false,      
            userName: "",
            userInitial: "U",
            attachments: [], 
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
        });

        useEffect(() => {
            if (this.chatEndRef.el) { this.chatEndRef.el.scrollIntoView({ behavior: "smooth" }); }
        }, () => [this.state.messages.length, this.state.isLoading]);
    }

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
                "odoo.ai.chat",
                [["user_id", "=", this.userService.userId]],
                ["id", "name", "write_date"],
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
        } catch (e) {
            this.state.messages = [{ role: "ai", content: _t("Không thể tải dữ liệu.") }];
        } finally {
            this.state.isLoading = false;
        }
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
                question: text,
                attachments: files,
                chat_id: this.state.activeChatId || false
            });

            if (res.chat_id && !this.state.activeChatId) {
                this.state.activeChatId = res.chat_id;
            }

            const msg = { role: "ai", content: res.answer };
            if (res.suggested_action) msg.suggested_action = res.suggested_action;
            this.state.messages.push(msg);

            await this._loadSidebarHistory();
        } catch (error) {
            this.state.messages.push({ role: "ai", content: _t("Lỗi kết nối: Không thể kết nối đến máy chủ AI.") });
        } finally {
            this.state.isLoading = false;
        }
    }

    async openSuggestedAction(xmlId) {
        try { await this.actionService.doAction(xmlId); } catch (e) { console.error("Lỗi mở báo cáo:", e); }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.sendMessage(); }
    }
}
AiChatWindow.template = "odoo_ai_assistant.AiChatWindowTemplate";
registry.category("actions").add("odoo_ai_assistant.AiChatClientAction", AiChatWindow);