#include "ui_component_24.h"
#include <iostream>

UIComponent24::UIComponent24() : model_(nullptr) {}

void UIComponent24::render() {
    if (model_) {
        std::cout << "Rendering UIComponent24 with model " << model_->getName() << "\n";
    }
}

void UIComponent24::setModel(Model24* model) {
    model_ = model;
}
