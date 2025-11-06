#include "ui_component_4.h"
#include <iostream>

UIComponent4::UIComponent4() : model_(nullptr) {}

void UIComponent4::render() {
    if (model_) {
        std::cout << "Rendering UIComponent4 with model " << model_->getName() << "\n";
    }
}

void UIComponent4::setModel(Model4* model) {
    model_ = model;
}
