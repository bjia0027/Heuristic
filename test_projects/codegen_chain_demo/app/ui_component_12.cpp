#include "ui_component_12.h"
#include <iostream>

UIComponent12::UIComponent12() : model_(nullptr) {}

void UIComponent12::render() {
    if (model_) {
        std::cout << "Rendering UIComponent12 with model " << model_->getName() << "\n";
    }
}

void UIComponent12::setModel(Model12* model) {
    model_ = model;
}
