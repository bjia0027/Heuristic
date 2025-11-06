#include "ui_component_8.h"
#include <iostream>

UIComponent8::UIComponent8() : model_(nullptr) {}

void UIComponent8::render() {
    if (model_) {
        std::cout << "Rendering UIComponent8 with model " << model_->getName() << "\n";
    }
}

void UIComponent8::setModel(Model8* model) {
    model_ = model;
}
