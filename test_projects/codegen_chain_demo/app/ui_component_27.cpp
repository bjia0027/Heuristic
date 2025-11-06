#include "ui_component_27.h"
#include <iostream>

UIComponent27::UIComponent27() : model_(nullptr) {}

void UIComponent27::render() {
    if (model_) {
        std::cout << "Rendering UIComponent27 with model " << model_->getName() << "\n";
    }
}

void UIComponent27::setModel(Model27* model) {
    model_ = model;
}
