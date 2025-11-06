#include "ui_component_10.h"
#include <iostream>

UIComponent10::UIComponent10() : model_(nullptr) {}

void UIComponent10::render() {
    if (model_) {
        std::cout << "Rendering UIComponent10 with model " << model_->getName() << "\n";
    }
}

void UIComponent10::setModel(Model10* model) {
    model_ = model;
}
