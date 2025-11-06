#pragma once
#include "model_3.h"

class UIComponent3 {
public:
    UIComponent3();
    void render();
    void setModel(Model3* model);
private:
    Model3* model_;
};
