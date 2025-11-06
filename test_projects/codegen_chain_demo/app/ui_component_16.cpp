#include "ui_component_16.h"
#include <iostream>

UIComponent16::UIComponent16() : model_(nullptr) {}

void UIComponent16::render() {
    if (model_) {
        std::cout << "Rendering UIComponent16 with model " << model_->getName() << "\n";
    }
}

void UIComponent16::setModel(Model16* model) {
    model_ = model;
}
