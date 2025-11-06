#include "ui_component_20.h"
#include <iostream>

UIComponent20::UIComponent20() : model_(nullptr) {}

void UIComponent20::render() {
    if (model_) {
        std::cout << "Rendering UIComponent20 with model " << model_->getName() << "\n";
    }
}

void UIComponent20::setModel(Model20* model) {
    model_ = model;
}
