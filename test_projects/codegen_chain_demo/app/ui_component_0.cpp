#include "ui_component_0.h"
#include <iostream>

UIComponent0::UIComponent0() : model_(nullptr) {}

void UIComponent0::render() {
    if (model_) {
        std::cout << "Rendering UIComponent0 with model " << model_->getName() << "\n";
    }
}

void UIComponent0::setModel(Model0* model) {
    model_ = model;
}
