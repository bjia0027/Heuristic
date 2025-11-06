#include "ui_component_28.h"
#include <iostream>

UIComponent28::UIComponent28() : model_(nullptr) {}

void UIComponent28::render() {
    if (model_) {
        std::cout << "Rendering UIComponent28 with model " << model_->getName() << "\n";
    }
}

void UIComponent28::setModel(Model28* model) {
    model_ = model;
}
