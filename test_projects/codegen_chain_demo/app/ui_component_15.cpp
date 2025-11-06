#include "ui_component_15.h"
#include <iostream>

UIComponent15::UIComponent15() : model_(nullptr) {}

void UIComponent15::render() {
    if (model_) {
        std::cout << "Rendering UIComponent15 with model " << model_->getName() << "\n";
    }
}

void UIComponent15::setModel(Model15* model) {
    model_ = model;
}
