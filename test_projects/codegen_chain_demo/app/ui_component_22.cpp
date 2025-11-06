#include "ui_component_22.h"
#include <iostream>

UIComponent22::UIComponent22() : model_(nullptr) {}

void UIComponent22::render() {
    if (model_) {
        std::cout << "Rendering UIComponent22 with model " << model_->getName() << "\n";
    }
}

void UIComponent22::setModel(Model22* model) {
    model_ = model;
}
