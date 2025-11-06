#include "ui_component_9.h"
#include <iostream>

UIComponent9::UIComponent9() : model_(nullptr) {}

void UIComponent9::render() {
    if (model_) {
        std::cout << "Rendering UIComponent9 with model " << model_->getName() << "\n";
    }
}

void UIComponent9::setModel(Model9* model) {
    model_ = model;
}
