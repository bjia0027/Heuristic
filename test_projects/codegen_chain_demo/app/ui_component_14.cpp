#include "ui_component_14.h"
#include <iostream>

UIComponent14::UIComponent14() : model_(nullptr) {}

void UIComponent14::render() {
    if (model_) {
        std::cout << "Rendering UIComponent14 with model " << model_->getName() << "\n";
    }
}

void UIComponent14::setModel(Model14* model) {
    model_ = model;
}
