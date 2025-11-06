#pragma once
#include "model_28.h"

class UIComponent28 {
public:
    UIComponent28();
    void render();
    void setModel(Model28* model);
private:
    Model28* model_;
};
