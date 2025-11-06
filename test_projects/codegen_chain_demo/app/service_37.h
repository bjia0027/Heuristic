#pragma once
#include <functional>
#include <vector>

class Service37 {
public:
    Service37();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
