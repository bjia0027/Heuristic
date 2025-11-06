#include "ui_component_26.h"
#include <iostream>

UIComponent26::UIComponent26() : model_(nullptr) {}

void UIComponent26::render() {
    if (model_) {
        std::cout << "Rendering UIComponent26 with model " << model_->getName() << "\n";
    }
}

void UIComponent26::setModel(Model26* model) {
    model_ = model;
}
