#include "ui_component_21.h"
#include <iostream>

UIComponent21::UIComponent21() : model_(nullptr) {}

void UIComponent21::render() {
    if (model_) {
        std::cout << "Rendering UIComponent21 with model " << model_->getName() << "\n";
    }
}

void UIComponent21::setModel(Model21* model) {
    model_ = model;
}
