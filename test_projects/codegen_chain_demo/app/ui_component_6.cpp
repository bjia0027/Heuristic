#include "ui_component_6.h"
#include <iostream>

UIComponent6::UIComponent6() : model_(nullptr) {}

void UIComponent6::render() {
    if (model_) {
        std::cout << "Rendering UIComponent6 with model " << model_->getName() << "\n";
    }
}

void UIComponent6::setModel(Model6* model) {
    model_ = model;
}
