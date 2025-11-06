#include "ui_component_13.h"
#include <iostream>

UIComponent13::UIComponent13() : model_(nullptr) {}

void UIComponent13::render() {
    if (model_) {
        std::cout << "Rendering UIComponent13 with model " << model_->getName() << "\n";
    }
}

void UIComponent13::setModel(Model13* model) {
    model_ = model;
}
