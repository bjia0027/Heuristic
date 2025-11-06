#include "ui_component_11.h"
#include <iostream>

UIComponent11::UIComponent11() : model_(nullptr) {}

void UIComponent11::render() {
    if (model_) {
        std::cout << "Rendering UIComponent11 with model " << model_->getName() << "\n";
    }
}

void UIComponent11::setModel(Model11* model) {
    model_ = model;
}
