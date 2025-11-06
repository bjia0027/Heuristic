#include "ui_component_1.h"
#include <iostream>

UIComponent1::UIComponent1() : model_(nullptr) {}

void UIComponent1::render() {
    if (model_) {
        std::cout << "Rendering UIComponent1 with model " << model_->getName() << "\n";
    }
}

void UIComponent1::setModel(Model1* model) {
    model_ = model;
}
