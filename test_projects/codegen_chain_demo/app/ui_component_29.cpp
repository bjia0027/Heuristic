#include "ui_component_29.h"
#include <iostream>

UIComponent29::UIComponent29() : model_(nullptr) {}

void UIComponent29::render() {
    if (model_) {
        std::cout << "Rendering UIComponent29 with model " << model_->getName() << "\n";
    }
}

void UIComponent29::setModel(Model29* model) {
    model_ = model;
}
