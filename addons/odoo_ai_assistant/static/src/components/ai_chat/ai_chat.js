/** @odoo-module **/
import { Component, useState, onWillStart, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AiChatWidget extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            isOpen: false, 
            messages: [{ role: "ai", content: "Xin chào! Tôi là AI. Tôi có thể giúp gì cho dự án của bạn?" }],
            inputText: "",
            isLoading: false
        });
        this.chatEndRef = useRef("chatEnd");

        onWillStart(async () => {
            const history = await this.orm.call("odoo.ai.chat", "get_history_for_ui", []);
            if (history.length > 0) {
                this.state.messages = [
                    { role: "ai", content: "Xin chào! Tôi là AI. Tôi có thể giúp gì cho dự án của bạn?" },
                    ...history
                ];
            }
        });

        useEffect(() => {
            if (this.state.isOpen && this.chatEndRef.el) {
                this.chatEndRef.el.scrollIntoView({ behavior: "smooth" });
            }
        }, () => [this.state.messages, this.state.isLoading, this.state.isOpen]);
    }

    toggleChat() {
        this.state.isOpen = !this.state.isOpen;
    }

    async sendMessage() {
        if (!this.state.inputText.trim()) return;
        const text = this.state.inputText;
        this.state.messages.push({ role: "user", content: text });
        this.state.inputText = "";
        this.state.isLoading = true;

        try {
            const res = await this.orm.call("odoo.ai.chat", "send_message_from_ui", [text]);
            this.state.messages.push({ role: "ai", content: res.answer });
        } catch (error) {
            this.state.messages.push({ role: "ai", content: "Lỗi kết nối đến máy chủ." });
        } finally {
            this.state.isLoading = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}

AiChatWidget.template = "odoo_ai_assistant.AiChatWidgetTemplate";
registry.category("main_components").add("odoo_ai_assistant.AiChatWidget", { Component: AiChatWidget });