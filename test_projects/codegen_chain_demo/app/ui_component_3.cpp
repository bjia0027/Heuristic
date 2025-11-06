#include "ui_component_3.h"
#include <iostream>

UIComponent3::UIComponent3() : model_(nullptr) {}

void UIComponent3::render() {
    if (model_) {
        std::cout << "Rendering UIComponent3 with model " << model_->getName() << "\n";
    }
}

void UIComponent3::setModel(Model3* model) {
    model_ = model;
}
