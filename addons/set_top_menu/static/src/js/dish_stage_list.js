/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Field } from "@web/views/fields/field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, useEffect, useState, useSubEnv } from "@odoo/owl";

/**
 * Form nhập liệu của khâu đang chọn ở cột phải.
 */
export class DishStageForm extends Component {
    static template = "set_top_menu.DishStageForm";
    static components = { Field };
    static props = {
        record: Object,
        title: String,
        fieldNodes: Object,
    };

    setup() {
        useSubEnv({ model: this.props.record.model });
    }

    fieldNode(name) {
        return Object.values(this.props.fieldNodes).find((node) => node.name === name);
    }

    fieldLabel(name) {
        return this.props.record.fields[name].string;
    }
}

/**
 * Widget Bước 2 hiển thị 2 cột: cột trái liệt kê các khâu của quy trình
 * đã chọn (số thứ tự + tên khâu), cột phải là form nhập liệu của khâu
 * đang chọn.
 */
export class DishStageList extends Component {
    static template = "set_top_menu.DishStageList";
    static components = { DishStageForm };
    static props = {
        ...standardFieldProps,
        views: Object,
        relatedFields: Object,
        string: { type: String, optional: true },
    };

    setup() {
        this.state = useState({ selectedId: null });
        useEffect(
            () => {
                // Giữ mọi dòng khâu ở chế độ nhập liệu khi form món ăn đang sửa,
                // để chuyển khâu không làm mất dữ liệu đã nhập.
                if (this.props.record.isInEdition) {
                    for (const stage of this.list.records) {
                        if (!stage.isInEdition) {
                            stage.switchMode("edit");
                        }
                    }
                } else {
                    for (const stage of this.list.records) {
                        if (stage.isInEdition && stage.resId) {
                            stage.switchMode("readonly");
                        }
                    }
                }
            },
            () => [
                this.props.record.isInEdition,
                this.list.records.map((stage) => this.stageKey(stage)).join("|"),
            ]
        );
        // Debug: khi chọn quy trình ở Bước 1, in ra console thông tin quy
        // trình và danh sách khâu đi kèm.
        useEffect(
            () => {
                const process = this.props.record.data.process_id;
                if (process && process[0]) {
                    console.log("[Bước 2] Quy trình sản xuất:", {
                        id: process[0],
                        ten_quy_trinh: process[1],
                    });
                    console.log(
                        "[Bước 2] Danh sách khâu:",
                        this.stages.map((stage) => ({
                            sequence: this.stageSequence(stage),
                            ma_khau: this.stageCode(stage),
                            ten_khau: this.stageName(stage),
                        }))
                    );
                }
            },
            () => [this.props.record.data.process_id]
        );
    }

    get list() {
        return this.props.record.data[this.props.name];
    }

    get stages() {
        return [...this.list.records].sort((a, b) => {
            const seq = this.stageSequence(a) - this.stageSequence(b);
            return seq || (a.id > b.id ? 1 : a.id < b.id ? -1 : 0);
        });
    }

    get selected() {
        return (
            this.stages.find((stage) => this.stageKey(stage) === this.state.selectedId) ||
            this.stages[0]
        );
    }

    get fieldNodes() {
        return this.props.views.form.fieldNodes;
    }

    stageKey(stage) {
        return String(stage.id);
    }

    stageSequence(stage) {
        return stage.data.sequence || 0;
    }

    stageCode(stage) {
        return stage.data.step_code || "";
    }

    stageName(stage) {
        // Tên khâu lấy từ field chữ thuần (related), luôn là chuỗi nên
        // không phụ thuộc định dạng tuple của many2one.
        if (stage.data.step_name) {
            return stage.data.step_name;
        }
        const step = stage.data.step_id;
        if (Array.isArray(step) && step[1]) {
            return step[1];
        }
        return "Khâu " + this.stageSequence(stage);
    }

    selectStage(stage) {
        this.state.selectedId = this.stageKey(stage);
    }
}

export const dishStageList = {
    component: DishStageList,
    supportedTypes: ["one2many"],
    useSubView: true,
    extractProps: ({ relatedFields, views, string }) => ({
        relatedFields,
        views,
        string,
    }),
};
registry.category("fields").add("dish_stage_list", dishStageList);
