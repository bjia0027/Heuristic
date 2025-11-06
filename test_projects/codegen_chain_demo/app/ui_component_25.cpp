#include "ui_component_25.h"
#include <iostream>

UIComponent25::UIComponent25() : model_(nullptr) {}

void UIComponent25::render() {
    if (model_) {
        std::cout << "Rendering UIComponent25 with model " << model_->getName() << "\n";
    }
}

void UIComponent25::setModel(Model25* model) {
    model_ = model;
}
