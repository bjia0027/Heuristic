#include "ui_component_23.h"
#include <iostream>

UIComponent23::UIComponent23() : model_(nullptr) {}

void UIComponent23::render() {
    if (model_) {
        std::cout << "Rendering UIComponent23 with model " << model_->getName() << "\n";
    }
}

void UIComponent23::setModel(Model23* model) {
    model_ = model;
}
