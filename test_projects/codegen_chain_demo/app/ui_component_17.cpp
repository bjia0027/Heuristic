#include "ui_component_17.h"
#include <iostream>

UIComponent17::UIComponent17() : model_(nullptr) {}

void UIComponent17::render() {
    if (model_) {
        std::cout << "Rendering UIComponent17 with model " << model_->getName() << "\n";
    }
}

void UIComponent17::setModel(Model17* model) {
    model_ = model;
}
