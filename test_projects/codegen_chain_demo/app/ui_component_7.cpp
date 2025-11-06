#include "ui_component_7.h"
#include <iostream>

UIComponent7::UIComponent7() : model_(nullptr) {}

void UIComponent7::render() {
    if (model_) {
        std::cout << "Rendering UIComponent7 with model " << model_->getName() << "\n";
    }
}

void UIComponent7::setModel(Model7* model) {
    model_ = model;
}
