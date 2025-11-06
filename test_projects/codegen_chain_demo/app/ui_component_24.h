#pragma once
#include "model_24.h"

class UIComponent24 {
public:
    UIComponent24();
    void render();
    void setModel(Model24* model);
private:
    Model24* model_;
};
