#pragma once
#include "service_22.h"
#include "model_22.h"
#include <memory>

class Controller22 {
public:
    Controller22();
    void initialize();
    void run();
private:
    std::unique_ptr<Service22> service_;
    std::shared_ptr<Model22> model_;
};
