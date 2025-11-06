#include "ui_component_18.h"
#include <iostream>

UIComponent18::UIComponent18() : model_(nullptr) {}

void UIComponent18::render() {
    if (model_) {
        std::cout << "Rendering UIComponent18 with model " << model_->getName() << "\n";
    }
}

void UIComponent18::setModel(Model18* model) {
    model_ = model;
}
