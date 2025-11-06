#include "ui_component_5.h"
#include <iostream>

UIComponent5::UIComponent5() : model_(nullptr) {}

void UIComponent5::render() {
    if (model_) {
        std::cout << "Rendering UIComponent5 with model " << model_->getName() << "\n";
    }
}

void UIComponent5::setModel(Model5* model) {
    model_ = model;
}
