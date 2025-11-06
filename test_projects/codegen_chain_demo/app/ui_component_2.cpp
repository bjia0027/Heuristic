#include "ui_component_2.h"
#include <iostream>

UIComponent2::UIComponent2() : model_(nullptr) {}

void UIComponent2::render() {
    if (model_) {
        std::cout << "Rendering UIComponent2 with model " << model_->getName() << "\n";
    }
}

void UIComponent2::setModel(Model2* model) {
    model_ = model;
}
